"""Qualified looked-card packets and exact native movement continuations."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef, TriggerEvent
from app.rules import context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

SPELLS = {
    "look at twice x cards from the top of your library. put x cards from among them into your hand and the rest into your graveyard. you lose x life": "stargaze",
    "look at the top six cards of your library. put up to two land cards from among them onto the battlefield tapped and the rest on the bottom of your library in a random order. if you put fewer than two lands onto the battlefield this way, proliferate a number of times equal to the difference": "expand",
    "look at the top x cards of your library. you may put any number of land and/or legendary permanent cards with mana value x or less from among them onto the battlefield. put the rest into your graveyard": "vow",
    "target player shuffles up to four target cards from their graveyard into their library. you look at the top four cards of your library, then put one of those cards into your hand and the rest on the bottom of your library in a random order": "witness",
    'reveal the top four cards of your library. you may put a creature card from among them onto the battlefield. it gains "at the beginning of your end step, return ~ to its owner\'s hand." then put the rest of the cards revealed this way on the bottom of your library in any order': "touch",
    "look at the top seven cards of your library. you may put a creature card from among them onto the battlefield. put the rest on the bottom of your library in a random order. when a creature is put onto the battlefield this way, it deals damage equal to its power to target creature an opponent controls": "invocation",
    "target player reveals the top four cards of their library. you choose two of those cards and put them into that player's graveyard. put the rest on top of their library in any order": "bamboozle",
    "look at the top ten cards of your library, exile up to two creature cards from among them, then shuffle. target opponent may choose one of the exiled cards and put it onto the battlefield under their control. put the rest onto the battlefield under your control": "dubious",
    "look at the top three cards of your library. you may put those cards on the bottom of your library in any order. if you do, return ~ to its owner's hand. otherwise, draw three cards": "petals",
    "look at the top four cards of your library. put one of them into your hand and the rest into your graveyard. you gain life equal to the greatest power among creature cards put into your graveyard this way": "taste",
    "look at the top card of your library. you may put it onto the battlefield if it's a creature card. if you don't, put it into your hand": "believe",
    "look at the top five cards of your library. you may reveal up to two creature and/or land cards from among them, then put the rest on the bottom of your library in a random order. put all land cards revealed this way onto the battlefield tapped and put all creature cards revealed this way into your hand": "zimone",
    "look at the top twenty cards of your library. you may reveal up to two creature cards from among them. if this spell was kicked, put the revealed cards onto the battlefield. otherwise, put the revealed cards into your hand. then shuffle": "debut",
}

DEFINITIONS = {
    "at the beginning of your end step, if you control a creature, look at the top seven cards of your library. then you may sacrifice a creature. if you do, you may put a creature card with mana value x or less from among those cards onto the battlefield, where x is 1 plus the sacrificed creature's mana value. put the rest on the bottom of your library in a random order.": (
        "ritual",
        "At the beginning of your end step, if you control a creature, you gain 1 life.",
    ),
    "whenever ~ enters or attacks, look at the top six cards of your library. you may put any number of equipment cards from among them onto the battlefield. put the rest on the bottom of your library in a random order. when you put one or more equipment onto the battlefield this way, you may attach one of them to a samurai you control.": (
        "gilgamesh",
        "Whenever ~ enters or attacks, you gain 1 life.",
    ),
    "{t}, sacrifice x clues: target opponent reveals the top x cards of their library. you may put a nonland permanent card with mana value x or less from among them onto the battlefield under your control. that player puts the rest on the bottom of their library in a random order.": (
        "lonis",
        "{T}, Sacrifice X Clues: Target opponent gains 1 life.",
    ),
    "whenever ~ attacks a player who controls eight or more lands, look at the top eight cards of your library. you may put a creature card from among them onto the battlefield tapped and attacking that player. put the rest on the bottom of your library in a random order.": (
        "owlbear",
        "Whenever ~ attacks a player, you gain 1 life.",
    ),
    "whenever ~ attacks, look at the top x cards of your library, where x is its power. you may put a permanent card with mana value x or less from among them onto the battlefield. put the rest on the bottom of your library in a random order.": (
        "woodwurm",
        "Whenever ~ attacks, you gain 1 life.",
    ),
    "whenever ~ or another ally you control enters, you may look at the top four cards of your library. if you do, reveal any number of ally cards from among them, then put those cards on top of your library in any order and the rest on the bottom in any order.": (
        "munda",
        "Whenever ~ or another Ally you control enters, you may gain 1 life.",
    ),
    "whenever ~ deals combat damage to a player, that player reveals the top two cards of their library. you choose one of those cards and put it into their graveyard.": (
        "beguiler",
        "Whenever ~ deals combat damage to a player, you gain 1 life.",
    ),
    "{r}, {t}: look at the top eight cards of your library. exile four of them at random, then put the rest on top of your library in any order.": (
        "librarian",
        "{R}, {T}: You gain 1 life.",
    ),
    "{3}, {t}: target player looks at the top three cards of their library, puts one of them back on top of their library, then exiles the rest.": (
        "cylix",
        "{3}, {T}: Target player gains 1 life.",
    ),
    "when ~ enters, look at the top six cards of your library. you may reveal up to two creature cards with mana value x or less from among them, where x is the number of creatures that convoked ~. put the revealed cards into your hand, then shuffle.": (
        "eos",
        "When ~ enters, you gain 1 life.",
    ),
    "when ~ enters, exile up to one target creature card from a graveyard. if a card is put into exile this way, look at the top three cards of your library, then put one of those cards into your hand and the rest into your graveyard.": (
        "appraiser",
        "When ~ enters, exile up to one target creature card from a graveyard. If a card is put into exile this way, exile up to one target creature card from a graveyard.",
    ),
    "whenever another permanent you control enters, look at the top card of your library. if it shares a card type with that permanent, you may reveal that card and put it into your hand.": (
        "amareth",
        "Whenever another permanent you control enters, you gain 1 life.",
    ),
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    mode = SPELLS.get(" ".join(body.lower().split()).rstrip("."))
    if mode is None or mode == "zimone":
        return None
    from app.rules import scripts

    target: Any = "player" if mode == "bamboozle" else "opponent" if mode == "dubious" else None
    if mode == "witness":
        found = scripts.parse_effects(
            "Target player shuffles up to four target cards from their graveyard into their library."
        )
        assert found is not None
        target = found[1]
    return [{"do": "qualified_packet", "mode": mode, "binding": "ref:qualified_packet"}], target, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    entry = DEFINITIONS.get(" ".join(scripts.self_text(ability.text, ch.name).lower().split()))
    if entry is None:
        return None
    mode, template = entry
    if mode == "appraiser":
        template = "When ~ enters, exile up to one target creature card from a graveyard."
    found = scripts.define(replace(ability, text=template), ch)
    if found is None:
        return None
    if mode == "owlbear":
        found = {**found, "cond": {**found.get("cond", {}), "defender_lands_min": 8}}
    return {**found, "effects": [{"do": "qualified_packet", "mode": mode, "binding": "ref:qualified_packet"}]}


def insert(ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    ctx["effects"][ctx["next"] : ctx["next"]] = es
    return True


def name(e: dict[str, Any], suffix: str = "") -> str:
    return e["binding"].removeprefix(context.PREFIX) + suffix


def follow(e: dict[str, Any], step: str, **kw: Any) -> dict[str, Any]:
    return {"do": "qualified_packet_" + step, "mode": e["mode"], "binding": e["binding"], **kw}


def key(what: str, cap: int | None = None) -> str:
    sel = selectors.parse(what)
    assert sel is not None, what
    if cap is not None:
        sel = selectors.replace(sel, compare=(*sel.compare, ("mv", "<=", cap)))
    return sel.key()


def look(e: dict[str, Any], n: Any, **kw: Any) -> dict[str, Any]:
    return {"do": "look_top", "n": n, "player": "you", "exact_look": True, "as": name(e, "_seen"), **kw}


def pick(e: dict[str, Any], n: Any = 1, **kw: Any) -> dict[str, Any]:
    return {"do": "pick_looked", "n": n, "optional": True, "as": name(e, "_picked"), **kw}


def restore(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    b = name(e, "_picked")
    receipt = context.refs(ctx).get(b, {})
    if "was" not in receipt:
        before = [ObjectRef.model_validate(r) for r in receipt.get("objects", [])]
        context.bind_moved(plan, ctx, b, before)
    arrived = [c for c in context.objects(plan, ctx, b) if plan.state.cards[c].zone.endswith(":battlefield")]
    context.bind_objects(plan, ctx, name(e, "_arrived"), arrived)
    owner = effects._looked(plan, ctx)[0]
    for cid in context.objects(plan, ctx, b):
        if plan.state.cards[cid].zone == f"{owner}:library" and cid not in ctx.get("looked", []):
            ctx.setdefault("looked", []).append(cid)
    return True


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, scripts, values

    mode = e["mode"]
    x = max(0, int(ctx.get("x") or 0))
    n, amount, to, rest, what = 4, 1, "hand", "bottom_random", None
    optional = True
    extra: dict[str, Any] = {}
    first: list[dict[str, Any]] = []
    final: list[dict[str, Any]] = []
    if mode == "stargaze":
        n, amount, rest, optional = 2 * x, x, "graveyard", False
        final = [{"do": "lose_life", "who": "you", "n": x}]
    elif mode == "ritual":
        return insert(
            ctx,
            [
                look(e, 7),
                {
                    "do": "optional_payment",
                    "who": "you",
                    "cost": "Sacrifice a creature",
                    "bind": name(e, "_paid"),
                },
                follow(e, "ritual"),
            ],
        )
    elif mode == "gilgamesh":
        n, amount, to, what = 6, 6, "battlefield", "Equipment card"
    elif mode == "expand":
        n, amount, to, what = 6, 2, "battlefield_tapped", "land card"
    elif mode == "vow":
        n, amount, to, rest = x, x, "battlefield", "graveyard"
        a = selectors.from_key(key("land card", x))
        b = selectors.from_key(key("legendary permanent card", x))
        extra["sel"] = selectors.Selector(
            card=True,
            zones=("library",),
            either=(selectors.replace(a, zones=()).key(), selectors.replace(b, zones=()).key()),
        ).key()
    elif mode == "lonis":
        n, to, what = x, "battlefield", "nonland permanent card"
        extra["sel"] = key(what, x)
    elif mode == "owlbear":
        n, to, what = 8, "battlefield_attacking", "creature card"
        extra["at"] = {"as": "that"}
    elif mode == "woodwurm":
        n = max(0, values.evaluate(plan, ctx, {"power": "self"}))
        to, what = "battlefield", "permanent card"
        extra["sel"] = key(what, n)
    elif mode == "witness":
        native = scripts.parse_effects(
            "Target player shuffles up to four target cards from their graveyard into their library."
        )
        assert native is not None
        first = native[0]
        optional = False
    elif mode == "munda":
        n, amount, to, rest, what = 4, 4, "top_any", "bottom_any", "Ally card"
        extra["reveal"] = True
    elif mode == "touch":
        n, to, rest, what = 4, "battlefield", "bottom_any", "creature card"
    elif mode == "invocation":
        n, to, what = 7, "battlefield", "creature card"
    elif mode == "bamboozle":
        n, amount, to, rest, optional = 4, 2, "graveyard", "top_any", False
    elif mode == "beguiler":
        n, to, rest, optional = 2, "graveyard", "stay", False
    elif mode == "librarian":
        return insert(ctx, [look(e, 8), follow(e, "random"), {"do": "rest_looked", "to": "top_any"}])
    elif mode == "cylix":
        n, to, rest, optional = 3, "top", "exile", False
    elif mode == "dubious":
        return insert(
            ctx,
            [
                look(e, 10),
                pick(e, 2, to="exile", sel=key("creature card")),
                {"do": "shuffle_library", "who": "you", "zones": []},
                follow(e, "dubious"),
            ],
        )
    elif mode == "petals":
        return insert(ctx, [look(e, 3), follow(e, "petals")])
    elif mode == "taste":
        n, rest, optional = 4, "graveyard", False
    elif mode == "believe":
        n, to, rest, what = 1, "battlefield", "stay", "creature card"
    elif mode == "zimone":
        # This recipe stays refused until its exact cross-zone overlap policy is verified.
        return True
    elif mode == "eos":
        n, amount, what = 6, 2, "creature card"
        extra.update(sel=key(what, values.evaluate(plan, ctx, {"convoked": True})), reveal=True)
        rest = "shuffle"
    elif mode == "debut":
        record = plan.rules.payments.get(ctx.get("source_object") or "")
        n, amount, what, to, rest = (
            20,
            2,
            "creature card",
            "battlefield" if record is not None and record.kicked else "hand",
            "shuffle",
        )
        extra["reveal"] = True
    elif mode == "appraiser":
        native = scripts.parse_effects("Exile up to one target creature card from a graveyard.")
        assert native is not None
        return insert(ctx, [{**native[0][0], "as": name(e, "_exiled")}, follow(e, "appraiser")])
    elif mode == "amareth":
        n, to, rest = 1, "hand", "stay"
        info = context.info(plan, ctx, "event")
        kinds = tuple(sorted(info[1].types)) if info is not None else ()
        extra["sel"] = selectors.Selector(
            card=True,
            zones=("library",),
            types=kinds,
            not_types=()
            if kinds
            else (
                "Artifact",
                "Creature",
                "Enchantment",
                "Land",
                "Planeswalker",
                "Instant",
                "Sorcery",
                "Kindred",
            ),
        ).key()
        extra["reveal"] = True
    else:
        return True
    if what is not None and "sel" not in extra:
        extra["sel"] = key(what)
    inspection = look(e, n)
    if mode in ("touch", "lonis", "bamboozle", "beguiler"):
        inspection["reveal"] = True
    if mode in ("lonis", "bamboozle", "cylix"):
        inspection["player"] = "target"
    if mode == "beguiler":
        inspection["player"] = "event_player"
    if mode == "cylix":
        inspection["viewer"] = "target"
        extra["chooser"] = "target"
    inspection_steps = [inspection]
    if mode in ("lonis", "bamboozle", "beguiler"):
        owners = effects._players(plan, ctx, "event_player" if mode == "beguiler" else "target")
        if not owners:
            return True
        inspection_steps = [{"do": "as_player", "player": owners[0]}, {**inspection, "player": "you"}, {"do": "as_player_end"}]
    es = [*first, *inspection_steps, pick(e, amount, to=to, optional=optional, **extra)]
    if to.startswith("battlefield"):
        es.append(follow(e, "restore"))
        if mode == "touch":
            es.append(follow(e, "after"))
    if rest in ("bottom_any", "bottom_random", "top_any", "graveyard", "exile"):
        es.append({"do": "rest_looked", "to": rest, **({"viewer": "target"} if mode in ("lonis", "cylix") else {}), **({"as": name(e, "_rest")} if mode == "taste" else {})})
    elif rest == "shuffle":
        es.append({"do": "shuffle_library", "who": "you", "zones": []})
    if mode in ("gilgamesh", "expand", "invocation", "taste", "believe", "amareth", "beguiler", "munda"):
        es.append(follow(e, "after"))
    return insert(ctx, [*es, *final])


def after(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, scripts, triggers

    mode = e["mode"]
    arrived = context.objects(plan, ctx, name(e, "_arrived"))
    if mode == "expand":
        n = sum(plan.ch(plan.state.cards[c]).is_land for c in arrived)
        return insert(ctx, [{"do": "proliferate", "who": "you"} for _ in range(max(0, 2 - n))])
    if mode == "touch":
        return insert(
            ctx,
            [
                {
                    "do": "grant",
                    "who": "ref:" + name(e, "_arrived"),
                    "keywords": [],
                    "abilities": [
                        "At the beginning of your end step, return this creature to its owner's hand."
                    ],
                    "duration": "permanent",
                }
            ],
        )
    if mode in ("invocation", "gilgamesh"):
        if not arrived:
            return True
        if mode == "invocation":
            native = scripts.parse_effects(
                "That creature deals damage equal to its power to target creature an opponent controls.",
                it="event",
            )
            assert native is not None
            ability = {
                "kind": "triggered",
                "trigger": "reflexive",
                "effects": native[0],
                **scripts.target_fields(native[1]),
                "optional": False,
            }
        else:
            arrived = [c for c in arrived if "Equipment" in plan.ch(plan.state.cards[c]).subtypes]
            if not arrived:
                return True
            ability = {
                "kind": "triggered",
                "trigger": "reflexive",
                "effects": [follow(e, "attach")],
                "target": None,
                "optional": True,
            }
        event = TriggerEvent(
            kind="reflexive",
            objects=[r for c in arrived if (r := context.ref_of(plan, c)) is not None],
            count=len(arrived),
        )
        triggers._add(
            plan,
            controller=ctx["controller"],
            source_card=ctx.get("source_card") or "",
            source_object=ctx.get("source_object") or "",
            name=ctx.get("name") or "",
            index=7300,
            definition=ability,
            event=event,
        )
        return True
    if mode == "taste":
        from app.rules import this_way

        powers = []
        for new, _ in this_way._matched(plan, ctx, {"this_way": "graveyard", "ref_count": name(e, "_rest")}):
            c = plan.state.cards.get(new["card"])
            if c is not None and c.zone.endswith(":graveyard") and plan.oid(c) == new["object_id"]:
                ch = plan.ch(c)
                if ch.is_creature and ch.pt is not None:
                    powers.append(ch.pt[0])
        return insert(ctx, [{"do": "gain_life", "who": "you", "n": max(0, max(powers, default=0))}])
    if mode == "believe":
        return insert(ctx, [{"do": "return_card", "who": "ref:" + name(e, "_seen"), "to": "hand"}])
    if mode in ("amareth", "beguiler", "munda"):
        return effects.hide_revealed(plan, ctx, {"refs": name(e, "_seen"), "zone": "library"})
    return True


def ritual(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    paid = name(e, "_paid")
    es = []
    if context.succeeded(ctx, paid):
        info = context.info(plan, ctx, paid)
        cap = 1 + int(info[1].mana_value) if info is not None else 1
        es = [pick(e, to="battlefield", sel=key("creature card", cap)), follow(e, "restore")]
    return insert(ctx, [*es, {"do": "rest_looked", "to": "bottom_random"}])


def appraiser(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import this_way

    if not this_way.count(plan, ctx, {"this_way": "exiled", "ref_count": name(e, "_exiled")}):
        return True
    return insert(
        ctx, [look(e, 3), pick(e, to="hand", optional=False), {"do": "rest_looked", "to": "graveyard"}]
    )


def random_pick(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import effects

    pool = effects._looked(plan, ctx)[1]
    from app.rules import randomness  # -- random choices (wave MBC-D) --
    chosen = randomness.sample(plan, plan.rng or secrets.SystemRandom(), pool, min(4, len(pool)), kind='card', player=ctx['controller'])
    return effects._picked(plan, ctx, pick(e, to="exile"), chosen)


def dubious(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    target = effects._players(plan, ctx, "target")
    if not target:
        return True
    return insert(
        ctx,
        [
            {
                "do": "return_choice",
                "who": "ref:" + name(e, "_picked"),
                "chooser": "target",
                "n": 1,
                "upto": True,
                "to": "choose",
                "as": name(e, "_chosen"),
            },
            follow(e, "dubious_after", player=target[0]),
        ],
    )


def dubious_after(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    selected = set(context.objects(plan, ctx, name(e, "_chosen")))
    rest = [c for c in context.objects(plan, ctx, name(e, "_picked")) if c not in selected]
    context.bind_objects(plan, ctx, name(e, "_others"), rest)
    return insert(
        ctx,
        [
            {"do": "as_player", "player": e["player"]},
            {"do": "return_card", "who": "ref:" + name(e, "_chosen"), "to": "battlefield", "under": "you"},
            {"do": "as_player_end"},
            {"do": "return_card", "who": "ref:" + name(e, "_others"), "to": "battlefield", "under": "you"},
        ],
    )


def petals(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    decide(
        plan,
        player=ctx["controller"],
        kind="confirm",
        prompt="Put the looked-at cards on the bottom and return this spell to hand?",
        options=[
            DecisionOption(id="yes", label="Put them on the bottom"),
            DecisionOption(id="no", label="Draw three cards"),
        ],
        resume={"step": "qualified_packet_petals", "ctx": ctx, "e": e},
    )
    return False


def resume_petals(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen[0] == "yes":
        insert(ctx, [{"do": "rest_looked", "to": "bottom_any"}, {"do": "bounce", "who": "self_stack"}])
    else:
        insert(ctx, [{"do": "draw", "who": "you", "n": 3}])
    effects.continue_effects(plan, ctx)


def attach(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments
    from app.rules.plan import decide

    pool = context.objects(plan, ctx, "event")
    pairs = {}
    for cid in pool:
        equipment = plan.state.cards[cid]
        if not equipment.zone.endswith(":battlefield") or "Equipment" not in plan.ch(equipment).subtypes:
            continue
        hosts = [
            c.id
            for c in plan.state.cards.values()
            if c.zone.endswith(":battlefield")
            and c.controller == ctx["controller"]
            and "Samurai" in plan.ch(c).subtypes
            and attachments.host_problem(plan, equipment, c.id, ctx["controller"]) is None
        ]
        if hosts:
            pairs[cid] = hosts
    if not pairs:
        return True
    decide(
        plan,
        player=ctx["controller"],
        kind="choose_one",
        prompt="Choose an Equipment put onto the battlefield this way",
        options=[DecisionOption(id=c, label=plan.ch(plan.state.cards[c]).name, card_id=c) for c in pairs],
        resume={"step": "qualified_packet_equipment", "ctx": ctx, "pairs": pairs},
    )
    return False


def resume_equipment(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.plan import decide

    cid = chosen[0]
    decide(
        plan,
        player=d.player,
        kind="choose_one",
        prompt="Choose a Samurai to attach it to",
        options=[
            DecisionOption(id=c, label=plan.ch(plan.state.cards[c]).name, card_id=c)
            for c in d.resume["pairs"][cid]
        ],
        resume={"step": "qualified_packet_samurai", "ctx": d.resume["ctx"], "equipment": cid},
    )


def resume_samurai(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments, effects

    attachments.attach(plan, d.resume["equipment"], chosen[0], d.player)
    effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {
    "qualified_packet": prepare,
    "qualified_packet_restore": restore,
    "qualified_packet_after": after,
    "qualified_packet_ritual": ritual,
    "qualified_packet_appraiser": appraiser,
    "qualified_packet_random": random_pick,
    "qualified_packet_dubious": dubious,
    "qualified_packet_dubious_after": dubious_after,
    "qualified_packet_petals": petals,
    "qualified_packet_attach": attach,
}
RESUME = {
    "qualified_packet_petals": resume_petals,
    "qualified_packet_equipment": resume_equipment,
    "qualified_packet_samurai": resume_samurai,
}
