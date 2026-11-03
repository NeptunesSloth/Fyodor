"""Exact reveal/exile packets, native cast-now continuations and simultaneous entries."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import context, selectors
from app.rules.plan import Plan

SPELLS = {
    "target permanent's controller sacrifices it. if the player does, they reveal cards from the top of their library until they reveal a permanent card that shares a card type with the sacrificed permanent, put that card onto the battlefield, then shuffle": "reweave",
    "exile target creature an opponent controls. that player reveals cards from the top of their library until a creature card is revealed. the player puts that card onto the battlefield, then shuffles the rest into their library": "blessed",
    "each player shuffles all creatures they own into their library. each player who shuffled a nontoken creature into their library this way reveals cards from the top of their library until they reveal a creature card, then puts that card onto the battlefield and the rest on the bottom of their library in a random order": "collision",
    "counter target instant or sorcery spell. its controller reveals cards from the top of their library until they reveal an instant or sorcery card. that player may cast that card without paying its mana cost. then the player shuffles": "spellshift",
    "shuffle your library, then reveal cards from the top of it until you reveal a nonland card. exile that card and put the rest on the bottom of your library in a random order. you may cast the exiled card without paying its mana cost": "creative",
    "for each player, choose target nonenchantment, nonland permanent that player controls. those permanents' owners shuffle them into their libraries. each player who controlled one of those permanents exiles cards from the top of their library until they exile a nonland card, then puts the rest on the bottom of their library in a random order. each player may cast the nonland card they exiled without paying its mana cost": "guff",
    "exile cards from the top of your library until you exile a legendary card. you may play that card for as long as this saga remains on the battlefield. put the rest of those exiled cards on the bottom of your library in a random order": "doctor",
    "choose up to three doctors. you may exile all other creatures. if you do, this saga deals 13 damage to you": "doctor4",
    "look at the top five cards of your library. exile one of them face down and put the rest on the bottom of your library in a random order. you may cast the exiled card without paying its mana cost if it's an instant spell with mana value 2 or less. if you don't, put that card into your hand": "discover",
}
DEFINITIONS = {
    "{1}{u}: ~'s owner shuffles it into their library. if that player does, they reveal cards from the top of that library until a card named mirror-mad phantasm is revealed. the player puts that card onto the battlefield and all other cards revealed this way into their graveyard": (
        "mirror",
        "{1}{U}: You gain 1 life.",
    ),
    "whenever a player casts a spell from their hand, that player exiles it, then exiles cards from the top of their library until they exile a card that shares a card type with it. that player may cast that card without paying its mana cost. then they put all cards exiled with ~ on the bottom of their library in a random order": (
        "storm",
        "Whenever a player casts a spell from their hand, you gain 1 life.",
    ),
    "whenever you cast your first instant, sorcery, or villain spell each turn, exile it, then exile cards from the top of your library until you exile a nonland card. ~ deals damage to each opponent equal to the difference between that spell's mana value and that nonland card's mana value. you may cast that card without paying its mana cost": (
        "loki",
        "Whenever you cast your first instant, sorcery, or Villain spell each turn, you gain 1 life.",
    ),
    "{1}{u/p}, {t}, exile a spell you control: target opponent reveals cards from the top of their library until they reveal a card with mana value equal to 1 plus the exiled spell's mana value. exile that card, then that player shuffles. you may cast that exiled card without paying its mana cost": (
        "pod",
        "{1}{U/P}, {T}, Exile a spell you control: Target opponent gains 1 life.",
    ),
    "whenever a land you control enters, exile cards from the top of your library until you exile a nonland card. you may cast that card this turn": (
        "bruntar",
        "Whenever a land you control enters, you gain 1 life.",
    ),
    "+2: target opponent exiles cards from the top of their library until they exile a nonland card. until end of turn, you may cast that card without paying its mana cost": (
        "bolas",
        "+2: Target opponent gains 1 life.",
    ),
    "whenever ~ attacks, look at the top x cards of your library, where x is ~'s power. you may exile an instant or sorcery card with mana value x or less from among them. put the rest on the bottom of your library in a random order. you may cast the exiled card without paying its mana cost": (
        "flamesage",
        "Whenever ~ attacks, you gain 1 life.",
    ),
    "whenever you cast a kraken, leviathan, octopus, or serpent spell from your hand, look at the top x cards of your library, where x is that spell's mana value. you may cast a spell with mana value less than x from among them without paying its mana cost. put the rest on the bottom of your library in a random order": (
        "kiora",
        "Whenever you cast a Kraken, Leviathan, Octopus, or Serpent spell from your hand, you gain 1 life.",
    ),
}


def norm(text: str) -> str:
    return " ".join(text.lower().split()).rstrip(".")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language, scripts

    mode = SPELLS.get(norm(body).replace("~", "this saga"))
    if mode is None:
        return None
    target = None
    first = []
    if mode == "reweave":
        target = language._one(language.ref("target permanent")[2])
    elif mode in ("blessed", "spellshift"):
        native = scripts.parse_effects(
            "Exile target creature an opponent controls."
            if mode == "blessed"
            else "Counter target instant or sorcery spell."
        )
        assert native is not None
        target = native[1]
    elif mode == "guff":
        native = scripts.parse_effects(
            "For each player, choose target nonenchantment, nonland permanent that player controls. Destroy those permanents."
        )
        assert native is not None
        first = native[0][:1]
        target = native[1]
    return [*first, {"do": "reveal_cast_packet", "mode": mode, "binding": "ref:reveal_cast"}], target, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    item = DEFINITIONS.get(norm(scripts.self_text(ability.text, ch.name)))
    if item is None:
        return None
    mode, template = item
    got = scripts.define(replace(ability, text=template), ch)
    return (
        {**got, "effects": [{"do": "reveal_cast_packet", "mode": mode, "binding": "ref:reveal_cast"}]}
        if got is not None
        else None
    )


def bind(e: dict[str, Any], suffix: str = "") -> str:
    return e["binding"].removeprefix("ref:") + suffix


def ref(e: dict[str, Any], suffix: str = "") -> str:
    return "ref:" + bind(e, suffix)


def step(e: dict[str, Any], stage: str, **kw: Any) -> dict[str, Any]:
    return {"do": "reveal_cast_stage", "mode": e["mode"], "binding": e["binding"], "stage": stage, **kw}


def insert(ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    ctx["effects"][ctx["next"] : ctx["next"]] = es
    return True


def sel(phrase: str, **kw: Any) -> str:
    parsed = selectors.parse(phrase)
    assert parsed is not None, phrase
    return selectors.replace(parsed, **kw).key()


def now(e: dict[str, Any], suffix: str = "_found", /, **kw: Any) -> dict[str, Any]:
    return {"do": "free_cast", "zone": "that", "who": ref(e, suffix), "exact_refs": True, **kw}


def grant(e: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {
        "do": "grant_play",
        "who": ref(e, "_found"),
        "play": False,
        "cast": True,
        "zone": "exile",
        "until": "end_of_turn",
        "from_exile": True,
        **kw,
    }


def reveal(
    plan: Plan, ctx: dict[str, Any], e: dict[str, Any], owner: str, key: str, *, suffix: str = ""
) -> str | None:
    from app.rules import effects

    controller = ctx["controller"]
    ctx["controller"] = owner
    try:
        effects.look_top(
            plan, ctx, {"n": 0, "player": "you", "until": key, "reveal": True, "exact_look": True}
        )
    finally:
        ctx["controller"] = controller
    shown = list(ctx.get("looked") or [])
    found = ctx.get("found")
    context.bind_objects(plan, ctx, bind(e, suffix + "_shown"), shown)
    context.bind_objects(plan, ctx, bind(e, suffix + "_found"), [found] if found in plan.state.cards else [])
    return found


def exile_packet(
    plan: Plan, ctx: dict[str, Any], e: dict[str, Any], owner: str, key: str, suffix: str = ""
) -> str | None:
    from app.rules import effects

    # Exact original top objects determine the matching prefix before native exile.
    ids = list(plan.state.zones.get(owner + ":library", []))
    at = effects._first_match(plan, ctx, ids, key, owner)
    shown = ids if at is None else ids[: at + 1]
    before = [r for c in shown if (r := context.ref_of(plan, c)) is not None]
    controller = ctx["controller"]
    ctx["controller"] = owner
    try:
        effects.exile_top(plan, ctx, {"n": len(shown), "player": "you"})
    finally:
        ctx["controller"] = controller
    context.bind_moved(plan, ctx, bind(e, suffix + "_shown"), before)
    valid = [
        c
        for c in context.objects(plan, ctx, bind(e, suffix + "_shown"))
        if plan.state.cards[c].zone.endswith(":exile")
    ]
    context.bind_objects(plan, ctx, bind(e, suffix + "_shown"), valid)
    found = shown[-1] if at is not None and shown and shown[-1] in valid else None
    context.bind_objects(plan, ctx, bind(e, suffix + "_found"), [found] if found else [])
    return found


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, payment_card_facts, values

    mode = e["mode"]
    you = ctx["controller"]
    es: list[dict[str, Any]] = []
    if mode in ("collision", "guff"):
        return multiplayer(plan, ctx, e)
    if mode == "doctor4":
        return insert(
            ctx,
            [
                {
                    "do": "return_choice",
                    "sel": sel("Doctor"),
                    "n": 3,
                    "upto": True,
                    "to": "choose",
                    "as": bind(e, "_doctors"),
                },
                step(e, "doctor4"),
            ],
        )
    if mode in ("flamesage", "kiora", "discover"):
        n = (
            5
            if mode == "discover"
            else max(
                0,
                values.evaluate(
                    plan, ctx, {"power": "self"} if mode == "flamesage" else {"mana_value": "event"}
                ),
            )
        )
        es = [{"do": "look_top", "n": n, "player": "you", "exact_look": True, "as": bind(e, "_shown")}]
        if mode == "kiora":
            es.extend([now(e, "_shown", mv_lt=n), {"do": "rest_looked", "to": "bottom_random"}])
        else:
            pick = {
                "do": "pick_looked",
                "n": 1,
                "to": "exile",
                "as": bind(e, "_found"),
                "optional": mode != "discover",
            }
            if mode == "flamesage":
                pick["sel"] = sel("instant or sorcery card", compare=(("mv", "<=", n),))
            else:
                pick["face_down"] = True
            es.extend(
                [
                    pick,
                    {"do": "rest_looked", "to": "bottom_random"},
                    now(
                        e,
                        **(
                            {
                                "filter": selectors.Selector(zones=("stack",), types=("Instant",)).key(),
                                "mv": 2,
                            }
                            if mode == "discover"
                            else {}
                        ),
                    ),
                ]
            )
            if mode == "discover":
                es.append({"do": "return_card", "who": ref(e, "_found"), "to": "hand"})
        return insert(ctx, es)
    if mode == "creative":
        return insert(ctx, [{"do": "shuffle_library", "who": "you"}, step(e, "creative")])
    owner = you
    key = sel("creature card")
    original = None
    if mode in ("storm", "loki"):
        info = context.info(plan, ctx, "event")
        if info is None:
            return True
        original = values.evaluate(plan, ctx, {"mana_value": "event"})
        if mode == "storm":
            players = effects._players(plan, ctx, "event_player")
            if not players:
                return True
            owner = players[0]
            key = selectors.Selector(zones=("library",), card=True, types=tuple(sorted(info[1].types))).key()
        else:
            key = sel("nonland card")
        effects.exile(plan, ctx, {"who": "event", "as": bind(e, "_original")})
    elif mode in ("reweave", "blessed", "spellshift"):
        cards = effects._cards(plan, ctx, "target")
        if not cards:
            return True
        card = plan.state.cards[cards[0]]
        owner = card.controller or card.owner
        if mode == "reweave":
            key = selectors.Selector(
                zones=("library",),
                card=True,
                types=tuple(sorted(plan.ch(card).types)),
                not_types=("Instant", "Sorcery"),
            ).key()
            effects.sacrifice(plan, ctx, {"who": "target", "by": "controller", "as": bind(e, "_sacrificed")})
            if not context._object_refs(ctx, bind(e, "_sacrificed"), was=True):
                return True
        else:
            effects.PRIMITIVES["exile" if mode == "blessed" else "counter"](plan, ctx, {"who": "target"})
            if mode == "spellshift":
                key = sel("instant or sorcery card")
    elif mode == "mirror":
        cards = effects._cards(plan, ctx, "self")
        if not cards:
            return True
        card = plan.state.cards[cards[0]]
        owner = card.owner
        oid = plan.oid(card)
        plan.do(
            {"type": "move", "card_ids": [card.id], "to": {"player": owner, "zone": "library"}}, actor=owner
        )
        moved = (
            card.id in plan.state.cards
            and plan.state.cards[card.id].zone == owner + ":library"
            and plan.oid(card.id) != oid
        )
        plan.do({"type": "shuffle", "player": owner, "zone": "library"}, actor=owner)
        if not moved:
            return True
        key = selectors.Selector(zones=("library",), card=True, extras=("name:Mirror-Mad Phantasm",)).key()
    elif mode in ("pod", "bolas"):
        owners = effects._players(plan, ctx, "target")
        if not owners:
            return True
        owner = owners[0]
        if mode == "pod":
            facts = payment_card_facts.get(plan, ctx, "exiled") or []
            if not facts:
                return True
            key = selectors.Selector(
                zones=("library",), card=True, compare=(("mv", "==", 1 + int(facts[0].mana_value)),)
            ).key()
        else:
            key = sel("nonland card")
    elif mode in ("bruntar", "doctor"):
        key = (
            sel("nonland card")
            if mode == "bruntar"
            else selectors.Selector(zones=("library",), card=True, supertypes=("Legendary",)).key()
        )
    # -- Star Trek (wave 111E) -- Exploratory Mission: "Then exile cards from the top of your library until you exile a nonland card. You may play
    # that card this turn." (Bruntar's packet, 406.1; "play", 305.1 / 601.1: a land back face of a modal double-faced card too, 712.12)
    if mode == "mission111e":
        exile_packet(plan, ctx, e, owner, sel("nonland card"))
        return insert(ctx, [grant(e, play=True)])
    if mode in ("storm", "loki", "bruntar", "bolas", "doctor"):
        found = exile_packet(plan, ctx, e, owner, key)
    else:
        found = reveal(plan, ctx, e, owner, key)
    if mode in ("reweave", "blessed", "mirror"):
        es = [
            {"do": "as_player", "player": owner},
            {"do": "return_card", "who": ref(e, "_found"), "to": "battlefield", "under": "you"},
            {"do": "as_player_end"},
        ]
        if mode == "mirror":
            es.append(step(e, "rest", owner=owner, to="graveyard"))
        else:
            es.append({"do": "shuffle_library", "who": "player:" + owner})
        es.append({"do": "hide_revealed", "refs": bind(e, "_shown"), "zone": "library"})
    elif mode == "spellshift":
        es = [
            {"do": "as_player", "player": owner},
            now(e),
            {"do": "as_player_end"},
            {"do": "shuffle_library", "who": "player:" + owner},
        ]
    elif mode == "pod":
        es = [
            {"do": "exile", "who": ref(e, "_found"), "as": bind(e, "_found")},
            {"do": "shuffle_library", "who": "player:" + owner},
            now(e),
        ]
    elif mode == "storm":
        es = [
            {"do": "as_player", "player": owner},
            now(e),
            {"do": "as_player_end"},
            step(e, "storm_rest", owner=owner),
        ]
    elif mode == "loki":
        diff = abs(int(original or 0) - (int(plan.ch(plan.state.cards[found]).mana_value) if found else 0))
        es = [{"do": "damage", "who": "each_opponent", "n": diff}, now(e)]
    elif mode in ("bruntar", "bolas"):
        es = [grant(e, free=mode == "bolas")]
    elif mode == "doctor":
        es = [
            grant(e, play=True, until="source_on_battlefield"),
            step(e, "rest", owner=owner, to="bottom_random", exiled=True),
        ]
    return insert(ctx, es)


def stage(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    tag = e["stage"]
    if tag == "creative":
        reveal(plan, ctx, e, ctx["controller"], sel("nonland card"))
        return insert(
            ctx,
            [
                {"do": "exile", "who": ref(e, "_found"), "as": bind(e, "_found")},
                step(e, "rest", owner=ctx["controller"], to="bottom_random"),
                now(e),
            ],
        )
    if tag in ("rest", "storm_rest"):
        pool = context.objects(plan, ctx, bind(e, "_shown"))
        if tag == "storm_rest":
            pool += context.objects(plan, ctx, bind(e, "_original"))
        pool = list(
            dict.fromkeys(
                c
                for c in pool
                if plan.state.cards[c].zone.endswith(
                    ":exile" if e.get("exiled") or tag == "storm_rest" else ":library"
                )
            )
        )
        if e.get("exiled"):
            pool = [c for c in pool if c not in context.objects(plan, ctx, bind(e, "_found"))]
        if tag == "storm_rest" or e.get("exiled"):
            effects.bottom_at_random(plan, e["owner"], pool, actor=e["owner"])
            return True
        ctx["looked"] = pool
        ctx["looked_owner"] = e["owner"]
        ctx["looked_objects"] = {c: plan.oid(c) for c in pool}
        return effects.rest_looked(plan, ctx, {"to": e["to"], "viewer": "player:" + e["owner"]})
    if tag == "doctor4":
        return insert(
            ctx,
            [
                {
                    "do": "optional_payment",
                    "who": "you",
                    "cost": "",
                    "ask": "exile all other creatures",
                    "bind": bind(e, "_accept"),
                },
                step(e, "doctor4_exile"),
            ],
        )
    if tag == "doctor4_exile":
        if not context.succeeded(ctx, bind(e, "_accept")):
            return True
        chosen = set(context.objects(plan, ctx, bind(e, "_doctors")))
        cards = [
            c.id
            for c in plan.state.cards.values()
            if c.id not in chosen
            and c.zone.endswith(":battlefield")
            and plan.in_game(c)
            and plan.ch(c).is_creature
        ]
        context.bind_objects(plan, ctx, bind(e, "_other"), cards)
        return insert(
            ctx, [{"do": "exile", "who": ref(e, "_other")}, {"do": "damage", "who": "you", "n": 13}]
        )
    if tag == "multi_rest":
        for item in e["packets"]:
            context.bind_objects(plan, ctx, bind(e, "_shown"), context.objects(plan, ctx, item["shown"]))
            stage(plan, ctx, {**e, "stage": "rest", "owner": item["owner"], "to": "bottom_random"})
        return True
    return True


def multiplayer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments, effects

    mode = e["mode"]
    players = list(plan.live())
    cards = []
    eligible = set()
    if mode == "collision":
        cards = [
            c.id
            for c in plan.state.cards.values()
            if c.zone.endswith(":battlefield") and plan.in_game(c) and plan.ch(c).is_creature
        ]
    else:
        cards = [
            t["id"]
            for group in ctx.get("groups", [])
            for t in group
            if t and t["id"] in plan.state.cards and plan.oid(t["id"]) == t.get("object_id")
        ]
    old = {
        c: (
            plan.oid(c),
            plan.state.cards[c].owner,
            plan.state.cards[c].controller,
            plan.state.cards[c].is_token,
        )
        for c in cards
    }
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "library"}}, actor=ctx["controller"])
    for cid, (oid, owner, controller, token) in old.items():
        if mode == "guff":
            eligible.add(controller)
        elif (
            not token
            and cid in plan.state.cards
            and plan.state.cards[cid].zone == owner + ":library"
            and plan.oid(cid) != oid
        ):
            eligible.add(owner)
    shufflers = players if mode == "collision" else sorted({v[1] for v in old.values()})
    for pid in shufflers:
        plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    packets = []
    entries = []
    es: list[dict[str, Any]] = []
    for i, pid in enumerate(players):
        if pid not in eligible:
            continue
        suffix = "_p" + str(i)
        found = (
            reveal(plan, ctx, e, pid, sel("creature card"), suffix=suffix)
            if mode == "collision"
            else exile_packet(plan, ctx, e, pid, sel("nonland card"), suffix)
        )
        shown = bind(e, suffix + "_shown")
        found_ref = ref(e, suffix + "_found")
        packets.append({"owner": pid, "shown": shown})
        if mode == "collision" and found:
            entries.append({"card": found, "player": pid, "actor": pid})
        if mode == "guff":
            # All exile/remaining placements precede all optional casts.
            rest = [c for c in context.objects(plan, ctx, shown) if c != found]
            effects.bottom_at_random(plan, pid, rest, actor=pid)
            es.extend(
                [
                    {"do": "as_player", "player": pid},
                    {"do": "free_cast", "zone": "that", "who": found_ref, "exact_refs": True},
                    {"do": "as_player_end"},
                ]
            )
    if mode == "guff":
        return insert(ctx, es)
    insert(ctx, [step(e, "multi_rest", packets=packets)])
    return attachments.enter(plan, entries, ctx)


PRIMITIVES = {"reveal_cast_packet": run, "reveal_cast_stage": stage}
